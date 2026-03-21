package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class ExtendedBufferedReader_5_1Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadLine_nonNullNonEmptyLine_updatesLastCharAndIncrementsCounter() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(new ExtendedBufferedReader(mockReader));

        // Mock underlying reader's read to simulate "Hello\n"
        when(mockReader.read(any(char[].class), anyInt(), anyInt()))
                .thenAnswer(invocation -> {
                    char[] buf = invocation.getArgument(0);
                    int offset = invocation.getArgument(1);
                    int length = invocation.getArgument(2);
                    String s = "Hello\n";
                    int toCopy = Math.min(length, s.length());
                    s.getChars(0, toCopy, buf, offset);
                    return toCopy;
                });

        // Call real method readLine()
        doCallRealMethod().when(spyReader).readLine();

        String line = spyReader.readLine();

        assertEquals("Hello", line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = lastCharField.getInt(spyReader);
        assertEquals('o', lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = lineCounterField.getInt(spyReader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_nonNullEmptyLine_lastCharNotUpdatedButCounterIncremented() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(new ExtendedBufferedReader(mockReader));

        // Mock underlying reader to return "\n"
        when(mockReader.read(any(char[].class), anyInt(), anyInt()))
                .thenAnswer(invocation -> {
                    char[] buf = invocation.getArgument(0);
                    int offset = invocation.getArgument(1);
                    int length = invocation.getArgument(2);
                    String s = "\n";
                    int toCopy = Math.min(length, s.length());
                    s.getChars(0, toCopy, buf, offset);
                    return toCopy;
                });

        // Set lastChar to UNDEFINED before call
        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        lastCharField.setInt(spyReader, ExtendedBufferedReader.UNDEFINED);

        // Call real method readLine()
        doCallRealMethod().when(spyReader).readLine();

        String line = spyReader.readLine();

        assertEquals("", line);

        int lastChar = lastCharField.getInt(spyReader);
        assertEquals(ExtendedBufferedReader.UNDEFINED, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = lineCounterField.getInt(spyReader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_nullLine_setsLastCharToEndOfStream() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(new ExtendedBufferedReader(mockReader));

        // Mock underlying reader to return -1 (end of stream)
        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenReturn(-1);

        // Call real method readLine()
        doCallRealMethod().when(spyReader).readLine();

        String line = spyReader.readLine();

        assertNull(line);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = lastCharField.getInt(spyReader);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = lineCounterField.getInt(spyReader);
        assertEquals(0, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_multipleCalls_incrementsLineCounter() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(new ExtendedBufferedReader(mockReader));

        // Setup a sequence of reads for "a\n", "b\n", then end of stream
        when(mockReader.read(any(char[].class), anyInt(), anyInt()))
                .thenAnswer(new org.mockito.stubbing.Answer<Integer>() {
                    private final String[] lines = {"a\n", "b\n"};
                    private int index = 0;
                    private int pos = 0;

                    @Override
                    public Integer answer(org.mockito.invocation.InvocationOnMock invocation) {
                        char[] buf = invocation.getArgument(0);
                        int offset = invocation.getArgument(1);
                        int length = invocation.getArgument(2);

                        if (index >= lines.length) {
                            return -1;
                        }

                        String currentLine = lines[index];
                        int remaining = currentLine.length() - pos;
                        if (remaining <= 0) {
                            index++;
                            pos = 0;
                            return answer(invocation);
                        }

                        int toCopy = Math.min(length, remaining);
                        currentLine.getChars(pos, pos + toCopy, buf, offset);
                        pos += toCopy;
                        return toCopy;
                    }
                });

        // Call real method readLine()
        doCallRealMethod().when(spyReader).readLine();

        assertEquals("a", spyReader.readLine());
        assertEquals("b", spyReader.readLine());
        assertNull(spyReader.readLine());

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = lineCounterField.getInt(spyReader);
        assertEquals(2, lineCounter);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = lastCharField.getInt(spyReader);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);
    }
}