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

class ExtendedBufferedReader_5_3Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testReadLine_nonNullNonEmptyLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        ExtendedBufferedReader spyReader = spy(extendedBufferedReader);

        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            String s = "testLine\n";
            s.getChars(0, s.length(), buf, 0);
            return s.length();
        });

        doCallRealMethod().when(spyReader).readLine();

        String result = spyReader.readLine();

        assertEquals("testLine", result);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(spyReader);
        assertEquals('e', lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(spyReader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_nonNullEmptyLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        ExtendedBufferedReader spyReader = spy(extendedBufferedReader);

        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenAnswer(invocation -> {
            char[] buf = invocation.getArgument(0);
            String s = "\n";
            s.getChars(0, s.length(), buf, 0);
            return s.length();
        });

        doCallRealMethod().when(spyReader).readLine();

        String result = spyReader.readLine();

        assertEquals("", result);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(spyReader);
        assertEquals(ExtendedBufferedReader.UNDEFINED, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(spyReader);
        assertEquals(1, lineCounter);
    }

    @Test
    @Timeout(8000)
    void testReadLine_nullLine() throws IOException, NoSuchFieldException, IllegalAccessException {
        ExtendedBufferedReader spyReader = spy(extendedBufferedReader);

        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenReturn(-1);

        doCallRealMethod().when(spyReader).readLine();

        String result = spyReader.readLine();

        assertNull(result);

        Field lastCharField = ExtendedBufferedReader.class.getDeclaredField("lastChar");
        lastCharField.setAccessible(true);
        int lastChar = (int) lastCharField.get(spyReader);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, lastChar);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        int lineCounter = (int) lineCounterField.get(spyReader);
        assertEquals(0, lineCounter);
    }
}