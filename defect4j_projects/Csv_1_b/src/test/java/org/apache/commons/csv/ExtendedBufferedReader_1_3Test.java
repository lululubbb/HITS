package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_1_3Test {

    private Reader mockReader;
    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testConstructor() {
        assertNotNull(extendedBufferedReader);
    }

    @Test
    @Timeout(8000)
    void testReadDelegatesToSuper() throws IOException {
        // Setup mockReader to return 65
        when(mockReader.read()).thenReturn(65);

        int result = extendedBufferedReader.read();

        assertEquals(65, result);
        verify(mockReader).read();
    }

    @Test
    @Timeout(8000)
    void testReadCharArray() throws IOException {
        char[] buf = new char[10];
        int offset = 2;
        int length = 5;

        // Setup mockReader to read chars into buf
        doAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            String data = "abcde";
            for (int i = 0; i < len; i++) {
                b[off + i] = data.charAt(i);
            }
            return len;
        }).when(mockReader).read(any(char[].class), eq(offset), eq(length));

        int readCount = extendedBufferedReader.read(buf, offset, length);

        assertEquals(5, readCount);
        assertArrayEquals(new char[] {0, 0, 'a', 'b', 'c', 'd', 'e', 0, 0, 0}, buf);
        verify(mockReader).read(any(char[].class), eq(offset), eq(length));
    }

    @Test
    @Timeout(8000)
    void testReadLine() throws IOException {
        // Setup mockReader to return "line1\n" when read() is called internally
        String line = "line1";
        char[] chars = (line + "\n").toCharArray();
        final int[] index = {0};
        when(mockReader.read()).thenAnswer(invocation -> {
            if (index[0] < chars.length) {
                return chars[index[0]++];
            }
            return -1;
        });

        String resultLine = extendedBufferedReader.readLine();

        assertEquals(line, resultLine);
    }

    @Test
    @Timeout(8000)
    void testLookAhead() throws NoSuchMethodException, SecurityException, IllegalAccessException, IllegalArgumentException, InvocationTargetException, IOException {
        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        // Setup mockReader to return 100
        when(mockReader.read()).thenReturn(100);

        int result = (int) lookAheadMethod.invoke(extendedBufferedReader);

        assertEquals(100, result);
        verify(mockReader).read();
    }

    @Test
    @Timeout(8000)
    void testReadAgain() throws NoSuchMethodException, SecurityException, IllegalAccessException, IllegalArgumentException, InvocationTargetException, IOException {
        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);

        // Setup mockReader to return 101
        when(mockReader.read()).thenReturn(101);

        int result = (int) readAgainMethod.invoke(extendedBufferedReader);

        assertEquals(101, result);
        verify(mockReader).read();
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber() throws NoSuchMethodException, SecurityException, IllegalAccessException, IllegalArgumentException, InvocationTargetException, NoSuchFieldException {
        Method getLineNumberMethod = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumberMethod.setAccessible(true);

        // Initially lineCounter is 0
        int lineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(0, lineNumber);

        // Use reflection to set lineCounter to a value and test again
        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        lineCounterField.setInt(extendedBufferedReader, 5);

        int updatedLineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(5, updatedLineNumber);
    }
}