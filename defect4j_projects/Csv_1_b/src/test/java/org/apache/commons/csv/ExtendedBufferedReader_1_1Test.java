package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Field;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_1_1Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

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
    void testRead() throws IOException {
        when(mockReader.read()).thenReturn((int) 'a');
        int result = extendedBufferedReader.read();
        assertEquals('a', result);
    }

    @Test
    @Timeout(8000)
    void testReadAgain() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, IOException {
        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);

        when(mockReader.read()).thenReturn((int) 'b');

        int result = (int) readAgainMethod.invoke(extendedBufferedReader);
        assertEquals('b', result);
    }

    @Test
    @Timeout(8000)
    void testReadCharArray() throws IOException {
        char[] buf = new char[10];
        when(mockReader.read(any(char[].class), anyInt(), anyInt())).thenAnswer(invocation -> {
            char[] b = invocation.getArgument(0);
            int off = invocation.getArgument(1);
            int len = invocation.getArgument(2);
            String s = "hello";
            int toCopy = Math.min(len, s.length());
            s.getChars(0, toCopy, b, off);
            return toCopy;
        });

        int readCount = extendedBufferedReader.read(buf, 0, 10);
        assertEquals(5, readCount);
        assertArrayEquals(new char[] {'h','e','l','l','o', '\0', '\0', '\0', '\0', '\0'}, buf);
    }

    @Test
    @Timeout(8000)
    void testReadLine() throws IOException {
        when(mockReader.read()).thenReturn((int) 'a', (int) '\n', ExtendedBufferedReader.END_OF_STREAM);
        String line = extendedBufferedReader.readLine();
        assertEquals("a", line);
    }

    @Test
    @Timeout(8000)
    void testLookAhead() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, IOException {
        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        when(mockReader.read()).thenReturn((int) 'c');

        int result = (int) lookAheadMethod.invoke(extendedBufferedReader);
        assertEquals('c', result);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, NoSuchFieldException {
        Method getLineNumberMethod = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumberMethod.setAccessible(true);

        Field lineCounterField = ExtendedBufferedReader.class.getDeclaredField("lineCounter");
        lineCounterField.setAccessible(true);
        lineCounterField.setInt(extendedBufferedReader, 42);

        int lineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(42, lineNumber);
    }
}